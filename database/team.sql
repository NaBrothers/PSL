create table IF NOT EXISTS `team` (
  `ID` int(11) NOT NULL auto_increment,
  `User` bigint NOT NULL,
  `Card` int(11) NOT NULL,
  `Position` int(11) NOT NULL,
  primary key(`id`)
) default charset = utf8;